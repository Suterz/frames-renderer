from PIL import Image,ImageDraw

from storyboard_renderer.compose import largest_component


def test_isolated_orange_keeps_its_body_and_removes_corner_surplus():
    image=Image.new("L",(80,80),0)
    d=ImageDraw.Draw(image)
    d.ellipse((18,19,64,66),fill=255)
    d.polygon([(2,51),(2,77),(16,77)],fill=255)
    d.line((39,19,45,8),fill=255,width=4)
    mask=largest_component(image)
    assert mask.getpixel((40,40))==255
    assert mask.getpixel((2,74))==0
    assert mask.getpixel((42,13))==255


def test_isolated_open_basket_does_not_fill_aperture():
    image=Image.new("L",(80,80),0)
    d=ImageDraw.Draw(image)
    d.ellipse((12,12,62,60),outline=255,width=4)
    d.rectangle((27,39,45,69),fill=0)
    d.rectangle((70,70,76,76),fill=255)
    mask=largest_component(image)
    assert mask.getpixel((38,25))==0
    assert mask.getpixel((37,13))==255
    assert mask.getpixel((72,72))==0
